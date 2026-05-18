# Sinktank v6 Circulation Test: 2026-04-04
"""
draw.py — ChemGrid 진입점 (Entry Point)
=========================================
canvas.py의 MoleculeCanvas와 main_window.py의 MainWindow를 사용합니다.

이전 버전에서는 이 파일에 MoleculeCanvas와 MainWindow가 모놀리스로 정의되어 있었으나,
Phase 6-4에서 모듈 분리가 완료되어 이제는 각 모듈에서 임포트합니다.

후방 호환: 다른 모듈이 `from draw import MoleculeCanvas`를 사용하는 경우를 위해
canvas.py에서 재임포트합니다.
"""
import sys
import os
import logging
import warnings

# [LITE-EXE-003 fix] PyInstaller console=False 빌드에서 stdout/stderr를 완전 억제
# MAGIC: hasattr(sys, '_MEIPASS') = PyInstaller 번들 실행 중 True
# print() 잔여 호출이 OS 레벨에서 GUI 영역에 텍스트 leak하는 문제 방지
if hasattr(sys, '_MEIPASS'):
    import io
    sys.stdout = io.StringIO()  # [MAGIC:NUL_STDOUT] PyInstaller 번들 stdout 완전 억제
    sys.stderr = io.StringIO()  # [MAGIC:NUL_STDERR] PyInstaller 번들 stderr 완전 억제

# --- matplotlib 경고 억제 (Glyph missing 등 UserWarning 팝업 방지) ---
# 반드시 matplotlib 임포트 전에 설정해야 함
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
warnings.filterwarnings('ignore', message='Glyph.*missing from.*font')

try:
    import matplotlib as _mpl
    # DejaVu Sans: 유니코드 수학 기호 지원, Malgun Gothic: 한글 폴백
    _mpl.rcParams['font.family'] = 'sans-serif'
    _mpl.rcParams['font.sans-serif'] = [
        'DejaVu Sans', 'Malgun Gothic', 'Arial', 'sans-serif'
    ]
    _mpl.rcParams['axes.unicode_minus'] = False  # 마이너스 부호 깨짐 방지
except ImportError:
    logging.getLogger(__name__).debug("matplotlib not installed, skipping rcParams setup")

logger = logging.getLogger(__name__)

# .env 파일에서 API 키 자동 로드
try:
    from dotenv import load_dotenv
    # 프로젝트 루트의 .env 파일 탐색 (src/app/ → chemgrid/)
    _env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
    elif os.path.exists(os.path.join(os.path.dirname(__file__), '.env')):
        load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError as e:
    logger.warning("python-dotenv not installed, skipping .env load: %s", e)

# 현재 스크립트 디렉토리를 sys.path에 추가 (모듈 검색 경로)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from PyQt6.QtWidgets import QApplication

# ========== 후방 호환 재임포트 ==========
# 다른 모듈이 `from draw import X`를 사용하는 경우를 위한 재수출
from canvas import MoleculeCanvas, CanvasMode, get_coord_key
from main_window import MainWindow
from ui_utils import load_icon, VERSION

# ==========================================
# 진입점
# ==========================================
if __name__ == "__main__":
    # [Issue Fix] Windows 작업표시줄 아이콘: AppUserModelID는 QApplication 생성 전에 설정해야 함
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('chemgrid.pro.v5')
    except (AttributeError, OSError) as e:
        logging.getLogger(__name__).debug("AppUserModelID 설정 실패 (비-Windows): %s", e)

    # [W22-02 fix] PyInstaller 번들에서 sys.argv에 bootloader 부가 인자가 포함될 수 있음.
    # QApplication(sys.argv) 시 Qt가 인식 불가 인자를 받으면 "Invalid command line" 팝업 표시.
    # 해결: Qt에는 argv[0] (실행파일명)만 전달. argparse는 sys.argv 전체를 별도 처리.
    # 참조: PyInstaller Issue #4886, Qt QTBUG-53920 [MAGIC:QAPP_ARGV_SLICE_1]
    _qt_argv = sys.argv[:1]  # argv[0]=실행파일명만 Qt에 전달
    app = QApplication(_qt_argv)

    # [M609 Rule Q] 글로벌 폰트 — Malgun Gothic 우선 (tofu 방지)
    # QApplication.setFont() 호출로 전체 위젯에 유니코드 지원 폰트 적용
    # Malgun Gothic: Windows 7+ 기본, 한글+영문+특수문자 완전 지원
    try:
        from PyQt6.QtGui import QFont, QFontDatabase
        _available_families = set(QFontDatabase.families())
        _FONT_PRIORITY_APP = [
            "Malgun Gothic", "NanumGothic", "Arial Unicode MS", "Arial"
        ]
        _resolved_app_font = next(
            (f for f in _FONT_PRIORITY_APP if f in _available_families),
            "Arial"
        )
        app.setFont(QFont(_resolved_app_font, 10))  # 10pt 기본, 각 위젯이 override
        import logging as _logging
        _logging.getLogger(__name__).info("[M609] 글로벌 앱 폰트: %s", _resolved_app_font)
    except Exception as _fe:
        import logging as _logging
        _logging.getLogger(__name__).warning("[M609] 글로벌 폰트 설정 실패: %s", _fe)

    # [Issue Fix] Windows 작업표시줄: QApplication 아이콘을 창 생성 전에 설정
    # MainWindow.__init__에서도 설정하지만, 작업표시줄은 app-level 아이콘을 먼저 참조
    _icon_path = os.path.join(_SCRIPT_DIR, "logo.ico")
    if os.path.exists(_icon_path):
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon(_icon_path))

    # ===== LITE-EXE-004: QSplashScreen — PyInstaller .exe 부팅 시 빈 화면 방지 =====
    # [W22-01 fix] PyInstaller .exe 기동 시 RDKit/PyQt6/matplotlib DLL 로딩에 최대 20초 소요.
    # (실측: 13~19초, 이전 명세 "~8초"는 과소 추정) splash는 MainWindow 완전 표시 시까지 유지.
    # _splash.finish(win) 패턴으로 splash가 먼저 사라지는 현상 방지됨.
    # 단계별 메시지: RDKit → PyQt6 UI → ChemGrid 모듈 순서로 진행 상황 표시.
    # logo.png를 splash 이미지로 사용 (ChemGrid.spec에 이미 번들됨).
    # Rule Q: 한국어+영어 병기 필수 / Rule O: 시각 품질
    from PyQt6.QtWidgets import QSplashScreen
    from PyQt6.QtGui import QPixmap, QColor
    from PyQt6.QtCore import Qt

    _splash_pix_path = os.path.join(_SCRIPT_DIR, "logo.png")
    _splash_size = (480, 300)  # 480×300 px — 적당한 splash 크기 [MAGIC:480x300]

    if os.path.exists(_splash_pix_path):
        _splash_pix = QPixmap(_splash_pix_path)
        # 고정 크기로 스케일 (원본 logo.png가 너무 크거나 작을 경우 대비)
        if not _splash_pix.isNull():
            _splash_pix = _splash_pix.scaled(
                _splash_size[0], _splash_size[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
    else:
        # logo.png 없을 경우 단색 배경 fallback
        _splash_pix = QPixmap(_splash_size[0], _splash_size[1])
        _splash_pix.fill(QColor("#1a2333"))  # 진한 남색 배경 [MAGIC:#1a2333]

    _splash = QSplashScreen(_splash_pix, Qt.WindowType.WindowStaysOnTopHint)
    _splash.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    # 메시지 스타일: 흰 텍스트, 하단 중앙 정렬 (Rule Q: 한국어+영어 병기)
    _splash_msg_flags = (
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
    )

    def _splash_msg(text: str) -> None:
        """splash 메시지 갱신 + processEvents로 즉시 화면 반영."""
        _splash.showMessage(text, _splash_msg_flags, QColor("white"))
        app.processEvents()

    _splash.show()
    app.processEvents()  # splash를 즉시 화면에 렌더링

    # [W22-01 fix] 단계별 진행 메시지 — 실제 로딩 단계를 학생에게 표시
    # 총 소요 시간 최대 20초 (실측: 13~19초) [MAGIC:BOOTSTRAP_MAX_20S]
    _splash_msg("ChemGrid 시작 중... (최대 20초 소요) / Starting ChemGrid...")
    app.processEvents()

    # 단계 1: 화학 엔진 모듈 로딩 알림 (RDKit DLL 언팩이 가장 오래 걸림)
    _splash_msg("화학 구조 엔진 로딩 중... / Loading chemistry engine (RDKit)...")
    app.processEvents()

    # 단계 2: UI 컴포넌트 생성 (MainWindow + 내부 모듈 연결)
    _splash_msg("ChemGrid UI 준비 중... / Loading UI components...")
    win = MainWindow()  # 실질적 로딩 시간 소모 지점
    app.processEvents()

    # 단계 3: 완료
    _splash_msg("ChemGrid 준비 완료! / Ready!")
    app.processEvents()

    win.show()
    # splash.finish(): main_window가 완전히 화면에 표시된 후 splash 제거.
    # WindowType.WindowStaysOnTopHint 때문에 finish() 전까지 splash가 항상 위에 유지됨.
    # — 이 패턴으로 "splash 사라진 후 빈 화면" 현상이 방지됨 [W22-01 확인됨]
    _splash.finish(win)
    # ===== END LITE-EXE-004 =====================================================

    # ========== CLI 자동 분자 로딩 (자동화 테스트용) ==========
    # Usage: python draw.py --auto-mol "benzene"
    #        python draw.py --auto-smiles "c1ccccc1"
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--auto-mol', type=str, default=None,
                        help='Auto-load molecule by name on startup')
    parser.add_argument('--auto-smiles', type=str, default=None,
                        help='Auto-load molecule by SMILES on startup')
    args, _ = parser.parse_known_args()

    if args.auto_mol:
        from PyQt6.QtCore import QTimer
        def _auto_load_mol():
            win.mol_name_input.setText(args.auto_mol)
            win._on_mol_name_submitted()
        QTimer.singleShot(1500, _auto_load_mol)
    elif args.auto_smiles:
        from PyQt6.QtCore import QTimer
        def _auto_load_smiles():
            win._draw_smiles_on_canvas(args.auto_smiles, "auto-test")
        QTimer.singleShot(1500, _auto_load_smiles)

    sys.exit(app.exec())
