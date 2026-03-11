"""
toolbar_setup.py — ChemGrid 툴바 구성 모듈
MainWindow의 __init__에서 툴바 설정 로직을 분리

[Phase 6-3 v4] 2줄 툴바 구조:
  tb1 (1줄): 로고, 파일, 내보내기, |, Undo, Redo
  addToolBarBreak()
  tb2 (2줄): Bond, 펜, 반응화살표, 지우개, 텍스트, 선택, 손, |, 대쉬, 웨지, |, 원소·기호, |, 전체지우기, 원소선택
"""
from PyQt6.QtWidgets import QToolBar, QMenu
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtCore import Qt, QSize

from ui_utils import load_icon


def setup_toolbars(window):
    """
    MainWindow의 두 개 툴바(tb, tb2)를 구성합니다.
    tb (1줄): 파일 관련 — 로고, 파일메뉴, 내보내기메뉴, Undo, Redo
    tb2 (2줄): 그리기 도구 — Bond, Pen, Arrow, Eraser, Text, Select, Hand, Dash, Wedge, 원소 등

    Args:
        window: MainWindow 인스턴스 (self)
    """
    window.setStyleSheet(
        "QToolButton { font-size: 13px; font-weight: bold; padding: 2px; } "
        "QMenu { font-size: 13px; }"
    )

    # ==========================================
    # 1단 툴바 (tb): 파일 관련
    # ==========================================
    window.tb = QToolBar("파일")
    window.tb.setMovable(False)
    window.tb.setIconSize(QSize(34, 34))
    window.tb.setMinimumHeight(58)
    window.addToolBar(window.tb)

    # 로고
    logo_action = QAction(load_icon("logo.png"), "ChemGrid", window)
    window.tb.addAction(logo_action)
    window.tb.addSeparator()

    # 파일 메뉴
    file_menu = QMenu("파일", window)
    file_menu.addAction("저장 (.chem)", window.save_file)
    file_menu.addAction("불러오기 (.chem)", window.load_file)
    file_btn = QAction("파일", window)
    file_btn.setMenu(file_menu)
    window.tb.addAction(file_btn)

    # 내보내기 메뉴
    export_menu = QMenu("내보내기", window)
    export_menu.addAction("PNG 저장", window.export_png)
    export_menu.addAction("PDF 저장", window.export_pdf)
    export_menu.addSeparator()
    export_menu.addAction("선택 영역 내보내기...", window.export_selection_dialog)
    export_menu.addAction("스펙트럼 PDF 내보내기...", window.export_spectrum_to_pdf)
    export_menu.addSeparator()
    export_menu.addAction("계산 히스토리 보기", window.show_calculation_history)
    export_menu.addAction("검증 보고서 생성", window.show_verification_report)
    export_btn = QAction("내보내기", window)
    export_btn.setMenu(export_menu)
    window.tb.addAction(export_btn)
    export_btn.setEnabled(False)
    window.export_btn = export_btn

    window.tb.addSeparator()

    # Undo / Redo
    window.tb.addAction(QAction(
        load_icon("undo.png", symbol_text="↺"), "Undo", window,
        triggered=window.cv.undo
    ))
    window.tb.addAction(QAction(
        load_icon("redo.png", symbol_text="↻"), "Redo", window,
        triggered=window.cv.redo
    ))

    # ==========================================
    # 줄바꿈 — 이 한 줄로 2줄 전환
    # ==========================================
    window.addToolBarBreak()

    # ==========================================
    # 2단 툴바 (tb2): 그리기 도구
    # ==========================================
    window.tb2 = QToolBar("그리기")
    window.tb2.setMovable(False)
    window.tb2.setIconSize(QSize(34, 34))
    window.tb2.setMinimumHeight(58)
    window.addToolBar(window.tb2)

    # 아이콘 매핑
    tool_icons = {
        "Select": ("select.png", None), "Hand": ("hand.png", None),
        "Pen": ("pen.png", None), "Eraser": ("eraser.png", None),
        "Bond": ("bond.png", None), "LonePair": ("", ".."),
        "Radical": ("", "·"), "Positive": ("", "+"), "Negative": ("", "-")
    }

    grp = QActionGroup(window)

    # --- 주요 도구: Bond, Pen, Arrow(신규), Eraser, Text(신규), Select, Hand ---
    primary_tools = ["Bond", "Pen"]
    for n in primary_tools:
        img_info = tool_icons.get(n, ("", n if len(n) <= 2 else None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb2.addAction(a)
        grp.addAction(a)
        if n == "Bond":
            a.setChecked(True)

    # [명령 4] 반응 화살표 (신규)
    window.arrow_action = QAction("→", window)
    window.arrow_action.setToolTip("반응 화살표")
    window.arrow_action.setCheckable(True)
    window.arrow_action.triggered.connect(window.create_handler("Arrow"))
    window.tb2.addAction(window.arrow_action)
    grp.addAction(window.arrow_action)

    # Eraser
    eraser_info = tool_icons.get("Eraser", ("", None))
    eraser_icon = load_icon(eraser_info[0], mode_name="Eraser", symbol_text=eraser_info[1])
    eraser_action = QAction(eraser_icon, "Eraser", window)
    eraser_action.setCheckable(True)
    eraser_action.triggered.connect(window.create_handler("Eraser"))
    window.tb2.addAction(eraser_action)
    grp.addAction(eraser_action)

    # [명령 4] 텍스트 도구 (신규)
    window.text_action = QAction("T", window)
    window.text_action.setToolTip("텍스트 상자")
    window.text_action.setCheckable(True)
    window.text_action.triggered.connect(window.create_handler("Text"))
    window.tb2.addAction(window.text_action)
    grp.addAction(window.text_action)

    # Select, Hand
    for n in ["Select", "Hand"]:
        img_info = tool_icons.get(n, ("", None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb2.addAction(a)
        grp.addAction(a)

    window.tb2.addSeparator()

    # --- 결합 변형: Dash, Wedge ---
    for n in ["Dash", "Wedge"]:
        img_info = tool_icons.get(n, ("", n if len(n) <= 2 else None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb2.addAction(a)
        grp.addAction(a)

    window.tb2.addSeparator()

    # --- 원소 및 화학 기호 도구 ---
    chem_tools = [
        "H", "R", "LonePair", "Radical", "Positive", "Negative",
        "O", "N", "P", "S", "F", "Cl", "Br", "I"
    ]
    for n in chem_tools:
        img_info = tool_icons.get(n, ("", n if len(n) <= 2 else None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb2.addAction(a)
        grp.addAction(a)

    window.tb2.addSeparator()

    # --- 유틸리티: 전체 지우기, 원소 선택 ---
    window.tb2.addAction(QAction("전체 지우기", window, triggered=window.clear_all))
    window.tb2.addAction(QAction("원소 선택", window, triggered=window.pick_el))
