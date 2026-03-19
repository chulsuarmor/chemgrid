"""
toolbar_setup.py — ChemGrid 툴바 구성 모듈
MainWindow의 __init__에서 툴바 설정 로직을 분리

[Phase 6-4 v5] 2줄 툴바 구조 (사용자 피드백 반영):
  tb1 (1줄, 메인): Select, Hand, Bond, Arrow, Pen, Text, Eraser | Dash, Wedge | 원소·기호 | Undo, Redo
  addToolBarBreak()
  tb2 (2줄, 보조, 높이 작음): 로고, 저장/불러오기, 내보내기, 전체 지우기, 원소 선택
"""
from PyQt6.QtWidgets import QToolBar, QMenu
from PyQt6.QtGui import QAction, QActionGroup, QFont, QPixmap, QPainter, QIcon
from PyQt6.QtCore import Qt, QSize

from ui_utils import load_icon


def _make_text_icon(text, size=40, font_size=22):
    """텍스트를 큰 글씨 아이콘으로 변환 (화살표/텍스트 도구용)"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.GlobalColor.black)
    painter.setFont(QFont("Arial", font_size, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


def setup_toolbars(window):
    """
    MainWindow의 두 개 툴바를 구성합니다.

    tb1 (1줄, 메인): 그리기 도구 — Select, Hand, Bond, Arrow, Pen, Text, Eraser,
                     | Dash, Wedge | 원소·기호 | Undo, Redo
    tb2 (2줄, 보조): 파일/유틸 — 로고, 저장/불러오기, 내보내기, 전체 지우기, 원소 선택

    Args:
        window: MainWindow 인스턴스 (self)
    """
    print("[TOOLBAR_V5] setup_toolbars loaded - 2-row layout with addToolBarBreak", flush=True)
    window.setWindowTitle("ChemGrid V5")   # ← 새 코드 적용 확인용 마커
    window.setStyleSheet(
        "QToolButton { font-size: 13px; font-weight: bold; padding: 2px; } "
        "QMenu { font-size: 13px; }"
    )

    # ==========================================
    # 1단 툴바 (tb): 메인 그리기 도구 (높이 58)
    # ==========================================
    window.tb = QToolBar("그리기")
    window.tb.setMovable(False)
    window.tb.setIconSize(QSize(34, 34))
    window.tb.setMinimumHeight(58)
    window.addToolBar(window.tb)

    # 아이콘 매핑
    tool_icons = {
        "Select": ("select.png", None), "Hand": ("hand.png", None),
        "Pen": ("pen.png", None), "Eraser": ("eraser.png", None),
        "Bond": ("bond.png", None), "LonePair": ("", ".."),
        "Radical": ("", "·"), "Positive": ("", "+"), "Negative": ("", "-")
    }

    grp = QActionGroup(window)

    # --- 주요 도구 순서: Select, Hand, Bond, Arrow, Pen, Text, Eraser ---
    # Select
    for n in ["Select", "Hand"]:
        img_info = tool_icons.get(n, ("", None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb.addAction(a)
        grp.addAction(a)

    # Bond (기본 선택)
    bond_info = tool_icons.get("Bond", ("", None))
    bond_icon = load_icon(bond_info[0], mode_name="Bond", symbol_text=bond_info[1])
    bond_action = QAction(bond_icon, "Bond", window)
    bond_action.setCheckable(True)
    bond_action.setChecked(True)
    bond_action.triggered.connect(window.create_handler("Bond"))
    window.tb.addAction(bond_action)
    grp.addAction(bond_action)

    # [F2] 반응 화살표 — 큰 아이콘 (→, 22pt)
    window.arrow_action = QAction(_make_text_icon("→", font_size=24), "Arrow", window)
    window.arrow_action.setToolTip("반응 화살표")
    window.arrow_action.setCheckable(True)
    window.arrow_action.triggered.connect(window.create_handler("Arrow"))
    window.tb.addAction(window.arrow_action)
    grp.addAction(window.arrow_action)

    # Pen
    pen_info = tool_icons.get("Pen", ("", None))
    pen_icon = load_icon(pen_info[0], mode_name="Pen", symbol_text=pen_info[1])
    pen_action = QAction(pen_icon, "Pen", window)
    pen_action.setCheckable(True)
    pen_action.triggered.connect(window.create_handler("Pen"))
    window.tb.addAction(pen_action)
    grp.addAction(pen_action)

    # [F2] 텍스트 도구 — 큰 아이콘 (T, 22pt)
    window.text_action = QAction(_make_text_icon("T", font_size=24), "Text", window)
    window.text_action.setToolTip("텍스트 상자")
    window.text_action.setCheckable(True)
    window.text_action.triggered.connect(window.create_handler("Text"))
    window.tb.addAction(window.text_action)
    grp.addAction(window.text_action)

    # Eraser
    eraser_info = tool_icons.get("Eraser", ("", None))
    eraser_icon = load_icon(eraser_info[0], mode_name="Eraser", symbol_text=eraser_info[1])
    eraser_action = QAction(eraser_icon, "Eraser", window)
    eraser_action.setCheckable(True)
    eraser_action.triggered.connect(window.create_handler("Eraser"))
    window.tb.addAction(eraser_action)
    grp.addAction(eraser_action)

    window.tb.addSeparator()

    # --- 결합 변형: Dash, Wedge ---
    for n in ["Dash", "Wedge"]:
        img_info = tool_icons.get(n, ("", n if len(n) <= 2 else None))
        img_path, sym = img_info
        icon = load_icon(img_path, mode_name=n, symbol_text=sym)
        a = QAction(icon, n, window)
        a.setCheckable(True)
        a.triggered.connect(window.create_handler(n))
        window.tb.addAction(a)
        grp.addAction(a)

    window.tb.addSeparator()

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
        window.tb.addAction(a)
        grp.addAction(a)

    window.tb.addSeparator()

    # Undo / Redo (메인 툴바 끝에 배치)
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
    # 2단 툴바 (tb2): 파일/유틸 (높이 작게)
    # ==========================================
    window.tb2 = QToolBar("파일")
    window.tb2.setMovable(False)
    window.tb2.setIconSize(QSize(20, 20))
    window.tb2.setMaximumHeight(36)
    window.tb2.setStyleSheet("QToolButton { font-size: 11px; padding: 1px 6px; }")
    window.addToolBar(window.tb2)

    # 로고 (작게)
    logo_action = QAction(load_icon("logo.png"), "", window)
    logo_action.setToolTip("ChemGrid")
    window.tb2.addAction(logo_action)
    window.tb2.addSeparator()

    # 저장/불러오기 메뉴
    file_menu = QMenu("저장/불러오기", window)
    file_menu.addAction("저장 (.chem)", window.save_file)
    file_menu.addAction("불러오기 (.chem)", window.load_file)
    file_btn = QAction("저장/불러오기", window)
    file_btn.setMenu(file_menu)
    window.tb2.addAction(file_btn)

    # 내보내기 메뉴
    export_menu = QMenu("내보내기", window)
    export_menu.addAction("PNG 저장", window.export_png)
    
    # [Automation] PDF 저장 단축키 (F9) 추가
    pdf_action = QAction("PDF 저장", window)
    pdf_action.triggered.connect(window.export_pdf)
    pdf_action.setShortcut("F9")
    pdf_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    export_menu.addAction(pdf_action)
    window.addAction(pdf_action)
    
    export_menu.addSeparator()
    export_menu.addAction("선택 영역 내보내기...", window.export_selection_dialog)
    export_menu.addAction("스펙트럼 PDF 내보내기...", window.export_spectrum_to_pdf)
    export_menu.addSeparator()
    export_menu.addAction("계산 히스토리 보기", window.show_calculation_history)
    export_menu.addAction("검증 보고서 생성", window.show_verification_report)
    export_btn = QAction("내보내기", window)
    export_btn.setMenu(export_menu)
    window.tb2.addAction(export_btn)
    export_btn.setEnabled(False)
    window.export_btn = export_btn

    # 신약개발 메뉴 — 학생 친화적: 리드 최적화를 최상단 배치
    drug_menu = QMenu("신약개발", window)
    drug_menu.addAction("리드 최적화 (신약 설계)", window.open_lead_optimizer_popup)
    drug_menu.addAction("ADMET 분석", window.open_admet_popup)
    drug_menu.addSeparator()
    adv_label = drug_menu.addAction("── 고급 (전문가용) ──")
    adv_label.setEnabled(False)
    drug_menu.addAction("AlphaFold 구조 예측", window.open_alphafold_popup)
    drug_menu.addAction("분자 도킹", window.open_docking_popup)
    drug_menu.addAction("신약 스크리닝", window.open_drug_screening_popup)
    drug_btn = QAction("신약개발", window)
    drug_btn.setMenu(drug_menu)
    window.tb2.addAction(drug_btn)

    window.tb2.addSeparator()

    # 전체 지우기
    window.tb2.addAction(QAction("전체 지우기", window, triggered=window.clear_all))

    # 원소 선택
    window.tb2.addAction(QAction("원소 선택", window, triggered=window.pick_el))
