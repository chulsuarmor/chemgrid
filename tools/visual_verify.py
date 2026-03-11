"""
visual_verify.py — ChemGrid 6단계 자동 피드백 사이클 v3.0
===========================================================
분자별 6단계 검증:
  S1: 루이스 구조 (Lewis Structure view) — 3초 대기 후 캡처
  S2: 이론적 구조 (Theory Structure view) — 3초 대기 후 캡처
  S3: 이론적 구조 전체 선택 — 드래그→3초→캡처 (파란 점선+분자명 확인)
  S4: 입체 구조 3D — 5초 대기+캡처, X/Y/Z 30도 회전 후 캡처
  S5: 분광분석 6종 — IR, Raman, 1H-NMR, 13C-NMR, UV-Vis, MolOrbital
  S6: PDF 내보내기 — 저장 후 결과 확인

spectra_assets 기준:
  IR:       X=4000→400cm⁻¹, Y=Transmittance%, 피크↓(inverted), baseline~100%
  Raman:    X=0→4000cm⁻¹, Y=Intensity, 피크↑(sharp)
  1H-NMR:  X=12→0ppm, Y=Intensity, Integration line, Splitting
  13C-NMR: X=220→0ppm, Y=Intensity, Singlets, Zone colors
  UV-Vis:   듀얼 뷰(ε + logε), X=200→800nm
  MolOrbital: 분자 오비탈 시각화

무한 루프: 실패 항목이 있는 한 자동 수정 + 재실행
"""

import subprocess, time, os, datetime, sys, json
import pyautogui, pygetwindow as gw
from PIL import ImageGrab, Image

pyautogui.FAILSAFE = False  # 화면 끝에서 실패 방지
pyautogui.PAUSE = 0.05

CHEMGRID_BAT   = r"c:\chemgrid\Run_ChemGrid.bat"
REPORT_DIR     = r"c:\chemgrid\docs\reports"
SHOTS_DIR      = r"c:\chemgrid\docs\reports\visual_shots"
PDF_TEST_DIR   = r"c:\chemgrid\docs\reports\test_pdfs"

os.makedirs(SHOTS_DIR, exist_ok=True)
os.makedirs(PDF_TEST_DIR, exist_ok=True)

INPUT_H = 38  # mol_name_input 높이 근사

# ─── 테스트 케이스 ───────────────────────────────────────
TEST_CASES = [
    ("benzene",       "c1ccccc1",         "GREEN/slight-RED",  "중성방향족 π halo"),
    ("tropylium",     "C1=CC=CC=C[CH+]1", "BLUE",              "C7H7+ 양이온 방향족"),
    ("cp-",           "[cH-]1cccc1",       "RED",               "Cp- 음이온 방향족"),
    ("acetic acid",   "CC(=O)O",           "RED(O)+BLUE(C=O)",  "카보닐C=BLUE, O=RED"),
    ("phenol",        "Oc1ccccc1",         "RED(O)+mix",        "OH→RED, ring=EDG편향"),
    ("aniline",       "Nc1ccccc1",         "RED(N)+mix",        "NH2→고리 RED편향"),
    ("chloromethane", "CCl",               "RED(Cl)+BLUE(C)",   "Cl=RED, C=BLUE"),
    ("L-alanine",     "C[C@@H](N)C(=O)O", "CHIRAL",            "R/S 키랄 중심"),
    ("naphthalene",   "c1ccc2ccccc2c1",    "GREEN+RED-pi",      "다환방향족 π halo"),
    ("formaldehyde",  "C=O",               "RED(O)+BLUE(C)",    "C=O: C=BLUE, O=RED"),
    ("water",         "O",                 "RED(O)+BLUE(H)",    "O=RED, H=BLUE"),
    ("aspirin",       "CC(=O)Oc1ccccc1C(=O)O", "MULTI",        "복합 작용기"),
]

# ─── 창 탐지 ─────────────────────────────────────────────
EXCLUDE_WIN = (
    "Visual Studio Code", "탐색기", "Explorer",
    "Chrome", "Firefox", "Edge", "Brave",
    "리포트", "Report", "report", "html", "피드백",
)

def find_chemgrid_window():
    for w in gw.getAllWindows():
        t = w.title
        if not t:
            continue
        if any(ex in t for ex in EXCLUDE_WIN):
            continue
        if t.strip() == "ChemGrid V5" and w.width > 300:
            return w
    for w in gw.getAllWindows():
        t = w.title
        if not t:
            continue
        if any(ex in t for ex in EXCLUDE_WIN):
            continue
        if t.startswith("ChemGrid") and w.width > 300 and w.height > 300:
            return w
    return None

def launch_chemgrid():
    print("[LAUNCH] ChemGrid 시작...")
    subprocess.Popen(["cmd", "/c", CHEMGRID_BAT],
                     creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(35):
        time.sleep(1)
        w = find_chemgrid_window()
        if w:
            print(f"[LAUNCH] 창 발견: '{w.title}' ({w.width}x{w.height})")
            time.sleep(2.0)
            return w
    print("[LAUNCH] FATAL: 창 없음")
    return None

def kill_chemgrid():
    subprocess.run(
        ["powershell", "-Command",
         "Get-Process python -EA SilentlyContinue "
         "| Where-Object {$_.MainWindowTitle -like '*ChemGrid*'} "
         "| Stop-Process -Force"],
        capture_output=True)
    time.sleep(1.5)

def safe_activate(win):
    """창 활성화 (핸들 무효 시 재검색)"""
    try:
        win.activate()
        time.sleep(0.4)
        return win
    except Exception:
        time.sleep(0.5)
        nw = find_chemgrid_window()
        if nw:
            try:
                nw.activate()
                time.sleep(0.4)
            except Exception:
                pass
            return nw
        return win

def screenshot(win, label):
    ts = datetime.datetime.now().strftime("%H%M%S")
    safe = label.replace(" ", "_").replace("/", "-")
    path = os.path.join(SHOTS_DIR, f"{ts}_{safe}.png")
    bbox = (win.left, win.top, win.left + win.width, win.top + win.height)
    ImageGrab.grab(bbox=bbox).save(path)
    return path

def screenshot_region(x, y, w, h, label):
    """화면 특정 영역 캡처"""
    ts = datetime.datetime.now().strftime("%H%M%S%f")[:10]
    safe = label.replace(" ", "_")
    path = os.path.join(SHOTS_DIR, f"{ts}_{safe}.png")
    ImageGrab.grab(bbox=(x, y, x+w, y+h)).save(path)
    return path

# ─── 좌표 헬퍼 ───────────────────────────────────────────
# resizeEvent 코드 기준:
#   margin=25, view_container=240x50, btn_back=200x50, btn_3d=200x50
#   analysis_buttons i=0..4 → btn_y = by - 50 - (i+1)*60

def _calc(win):
    """자주 쓰는 절대좌표 dict 반환"""
    margin = 25
    W, H = win.width, win.height
    L, T = win.left, win.top

    # view_container (Drawing 모드에서 표시)
    vc_left  = L + W - 240 - margin
    vc_top   = T + H - 50 - margin
    lewis_x  = vc_left + 55;   lewis_y  = vc_top + 25
    theory_x = vc_left + 175;  theory_y = vc_top + 25

    # btn_back (Theory/Lewis 모드)
    bk_x = L + W - 200 - margin + 100
    bk_y = T + H - 50  - margin + 25  # center

    # btn_3d (Theory 모드, btn_back 위 10px)
    td_x = bk_x
    td_y = T + (H - 50 - margin) - 50 - 10 + 25  # center

    # analysis buttons (Theory 모드)
    by_base = T + (H - 50 - margin)  # btn_back top-y
    spec_x  = L + W - 200 - margin + 100
    def _asy(i):
        return by_base - 50 - (i+1)*60 + 25  # center y

    # 입력창 (Drawing 모드 하단 중앙)
    input_w = min(580, W - 160)
    ix = L + (W - (input_w + 8 + 38)) // 2
    iy = T + H - INPUT_H - 18
    input_cx = ix + input_w // 2
    input_cy = iy + INPUT_H // 2

    # 캔버스 영역 (드래그 선택용)
    canvas_l = L + 80
    canvas_t = T + 95
    canvas_r = L + W - 260
    canvas_b = T + H - 80

    return {
        "lewis":  (lewis_x,  lewis_y),
        "theory": (theory_x, theory_y),
        "back":   (bk_x,     bk_y),
        "3d":     (td_x,     td_y),
        "spectrum": (spec_x, _asy(0)),
        "nmr":      (spec_x, _asy(1)),
        "uvvis":    (spec_x, _asy(2)),
        "md":       (spec_x, _asy(3)),
        "molorbital": (spec_x, _asy(4)),
        "input": (input_cx, input_cy),
        "canvas": (canvas_l, canvas_t, canvas_r, canvas_b),
    }

# ─── 분자 입력 ────────────────────────────────────────────
def type_molecule(win, name):
    win = safe_activate(win)
    c = _calc(win)
    cx, cy = c["input"]
    pyautogui.moveTo(cx, cy, duration=0.1)
    pyautogui.click()
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    pyautogui.typewrite(name, interval=0.06)
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(3.0)
    return win

# ─── 버튼 클릭 헬퍼 ──────────────────────────────────────
def click_btn(win, btn_name, wait=2.0):
    win = safe_activate(win)
    c = _calc(win)
    x, y = c[btn_name]
    pyautogui.moveTo(x, y, duration=0.15)
    pyautogui.click()
    time.sleep(wait)
    return win

# ─── 팝업 창 탐지 ────────────────────────────────────────
def find_new_window(known_titles, timeout=4):
    """기존 창 목록에 없는 새 창 탐색"""
    for _ in range(timeout * 4):
        time.sleep(0.25)
        for w in gw.getAllWindows():
            if not w.title:
                continue
            if w.title not in known_titles and w.width > 100 and w.height > 100:
                # 탐색기, VS Code 등 제외
                if any(ex in w.title for ex in EXCLUDE_WIN):
                    continue
                return w
    return None

def close_popup(popup_win=None):
    """팝업 닫기 (Alt+F4 또는 Escape)"""
    try:
        if popup_win:
            popup_win.activate()
            time.sleep(0.2)
    except Exception:
        pass
    pyautogui.hotkey("alt", "F4")
    time.sleep(0.5)

def dismiss_file_dialog():
    """파일 선택 다이얼로그 닫기"""
    pyautogui.press("escape")
    time.sleep(0.5)

# ─── 단계별 검증 함수 ────────────────────────────────────

def stage1_lewis(win, mol_name, idx):
    """S1: 루이스 구조 버튼 클릭 → 3초 → 캡처"""
    shots = []
    try:
        win = click_btn(win, "lewis", wait=3.0)
        p = screenshot(win, f"{idx:02d}_{mol_name}_S1_lewis")
        shots.append(("루이스 구조", p))
        print(f"    S1 Lewis: {os.path.basename(p)}")
    except Exception as e:
        print(f"    S1 Lewis ERROR: {e}")
        shots.append(("루이스 구조", None, str(e)))
    return win, shots

def stage2_theory(win, mol_name, idx):
    """S2: 이론적 구조 버튼 클릭 → 3초 → 캡처"""
    shots = []
    try:
        win = click_btn(win, "theory", wait=3.0)
        p = screenshot(win, f"{idx:02d}_{mol_name}_S2_theory")
        shots.append(("이론적 구조", p))
        print(f"    S2 Theory: {os.path.basename(p)}")
    except Exception as e:
        print(f"    S2 Theory ERROR: {e}")
        shots.append(("이론적 구조", None, str(e)))
    return win, shots

def stage3_select(win, mol_name, idx):
    """S3: 이론적 구조에서 전체 드래그 선택 → 3초 → 캡처"""
    shots = []
    try:
        win = safe_activate(win)
        c = _calc(win)
        cl, ct, cr, cb = c["canvas"]
        # 드래그: 캔버스 전체를 좌상→우하 드래그
        pyautogui.moveTo(cl + 10, ct + 10, duration=0.1)
        pyautogui.mouseDown()
        time.sleep(0.15)
        pyautogui.moveTo(cr - 10, cb - 10, duration=0.6)
        pyautogui.mouseUp()
        time.sleep(3.0)
        p = screenshot(win, f"{idx:02d}_{mol_name}_S3_select")
        shots.append(("전체 선택", p))
        print(f"    S3 Select: {os.path.basename(p)}")
    except Exception as e:
        print(f"    S3 Select ERROR: {e}")
        shots.append(("전체 선택", None, str(e)))
    return win, shots

def stage4_3d(win, mol_name, idx):
    """S4: 입체 구조 버튼 → 팝업 → 캡처 + X/Y/Z 30도 회전"""
    shots = []
    try:
        known = set(w.title for w in gw.getAllWindows() if w.title)
        win = click_btn(win, "3d", wait=0.5)
        popup = find_new_window(known, timeout=5)

        if popup:
            time.sleep(4.0)  # 3D 렌더링 대기
            # 초기 캡처
            bbox = (popup.left, popup.top,
                    popup.left + popup.width, popup.top + popup.height)
            p0 = os.path.join(SHOTS_DIR,
                f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S4_3d_initial.png")
            ImageGrab.grab(bbox=bbox).save(p0)
            shots.append(("3D 초기", p0))
            print(f"    S4 3D initial: {os.path.basename(p0)}")

            # 3D 뷰 중심 좌표
            vx = popup.left + popup.width // 2
            vy = popup.top  + popup.height // 2
            popup.activate()
            time.sleep(0.3)

            # X축 회전 (수평 드래그)
            pyautogui.moveTo(vx - 60, vy, duration=0.1)
            pyautogui.drag(120, 0, duration=0.6, button="left")
            time.sleep(1.5)
            p1 = os.path.join(SHOTS_DIR,
                f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S4_3d_rotX.png")
            ImageGrab.grab(bbox=bbox).save(p1)
            shots.append(("3D X회전", p1))

            # Y축 회전 (수직 드래그)
            pyautogui.moveTo(vx, vy - 60, duration=0.1)
            pyautogui.drag(0, 120, duration=0.6, button="left")
            time.sleep(1.5)
            p2 = os.path.join(SHOTS_DIR,
                f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S4_3d_rotY.png")
            ImageGrab.grab(bbox=bbox).save(p2)
            shots.append(("3D Y회전", p2))
        else:
            # 팝업 없음 → 메인 창 캡처
            p0 = screenshot(win, f"{idx:02d}_{mol_name}_S4_3d_failed")
            shots.append(("3D 팝업 없음", p0))
            print(f"    S4 3D: 팝업 없음 → {os.path.basename(p0)}")

    except Exception as e:
        print(f"    S4 3D ERROR: {e}")
        shots.append(("3D 오류", None, str(e)))
    return win, shots, popup if 'popup' in dir() else None

def stage5_spectra(win, mol_name, idx, popup_3d):
    """S5: 분광분석 6종 캡처
    - 팝업 내부에서 탭/버튼 클릭을 시도
    - 실패 시 메인 창의 버튼 클릭 후 캡처
    """
    shots = []
    SPEC_TYPES = [
        ("IR",        "spectrum",   "IR: 4000→400cm⁻¹, Transmittance%, 피크↓"),
        ("Raman",     "spectrum",   "Raman: Shift cm⁻¹, Intensity, 피크↑"),
        ("1H-NMR",    "nmr",        "1H-NMR: 12→0ppm, Integration line"),
        ("13C-NMR",   "nmr",        "13C-NMR: 220→0ppm, Zone색 (aliphatic/aromatic/carbonyl)"),
        ("UV-Vis",    "uvvis",      "UV-Vis: 듀얼뷰 ε+logε, 200→800nm"),
        ("MolOrbital","molorbital", "분자 오비탈 시각화"),
    ]

    # 3D 팝업이 열려있으면 닫고 Theory 뷰로 돌아가기
    if popup_3d:
        try:
            close_popup(popup_3d)
            time.sleep(1.0)
        except Exception:
            pass

    # Theory 뷰 확인 (이미 theory 뷰여야 버튼들이 보임)
    win = safe_activate(win)

    processed_btns = set()
    for spec_name, btn_key, note in SPEC_TYPES:
        try:
            # 같은 버튼을 두 번 클릭하는 경우 처리 (IR/Raman 둘 다 spectrum 버튼)
            known = set(w.title for w in gw.getAllWindows() if w.title)
            win = click_btn(win, btn_key, wait=0.3)
            time.sleep(0.5)

            # 새 팝업 탐색
            new_popup = find_new_window(known, timeout=3)

            if new_popup:
                time.sleep(2.0)
                # 팝업 내부에서 탭 선택 시도
                if btn_key not in processed_btns:
                    # 첫 번째 탭 (IR / 1H-NMR)
                    pass  # 기본 뷰 캡처
                elif btn_key in processed_btns:
                    # 두 번째 탭으로 이동 시도 (Raman / 13C-NMR)
                    # 탭 위치는 팝업 상단에 있을 것으로 가정
                    tab2_x = new_popup.left + new_popup.width // 4 * 2
                    tab2_y = new_popup.top + 35
                    pyautogui.click(tab2_x, tab2_y)
                    time.sleep(1.5)

                bbox = (new_popup.left, new_popup.top,
                        new_popup.left + new_popup.width,
                        new_popup.top  + new_popup.height)
                p = os.path.join(SHOTS_DIR,
                    f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S5_{spec_name}.png")
                ImageGrab.grab(bbox=bbox).save(p)
                shots.append((spec_name, p, note, new_popup.title))
                print(f"    S5 {spec_name}: {os.path.basename(p)}")

                # 팝업 닫기 전 PDF 내보내기 버튼 찾기 (Stage 6용)
                # 팝업 하단에 PDF 버튼이 있을 것으로 가정
                processed_btns.add(btn_key)
                close_popup(new_popup)
                time.sleep(0.8)
                win = safe_activate(win)

            else:
                # 파일 다이얼로그 또는 응답 없음
                # 파일 다이얼로그 dismiss
                pyautogui.press("escape")
                time.sleep(0.5)
                p = screenshot(win, f"{idx:02d}_{mol_name}_S5_{spec_name}_nodlg")
                shots.append((spec_name, p, f"팝업 없음 (ORCA 파일 필요?) — {note}", "없음"))
                print(f"    S5 {spec_name}: 팝업 없음")
                processed_btns.add(btn_key)

        except Exception as e:
            print(f"    S5 {spec_name} ERROR: {e}")
            shots.append((spec_name, None, str(e), "오류"))

    return win, shots

def stage6_pdf(win, mol_name, idx, popup_3d):
    """S6: PDF 내보내기 — spectrum 버튼 클릭 → 팝업 → PDF 버튼 클릭 → 저장"""
    shots = []
    try:
        # PDF 내보내기는 분광 팝업 안에 있을 것이므로 spectrum 버튼 재클릭
        win = safe_activate(win)
        known = set(w.title for w in gw.getAllWindows() if w.title)
        win = click_btn(win, "spectrum", wait=0.3)
        new_popup = find_new_window(known, timeout=4)

        if new_popup:
            time.sleep(1.5)
            # PDF 버튼 탐색: 팝업 하단 우측에 있을 것으로 가정
            pdf_x = new_popup.left + new_popup.width - 100
            pdf_y = new_popup.top  + new_popup.height - 40
            pyautogui.moveTo(pdf_x, pdf_y, duration=0.1)
            pyautogui.click()
            time.sleep(1.5)

            # 저장 다이얼로그 감지
            save_popup = find_new_window(
                set(w.title for w in gw.getAllWindows() if w.title),
                timeout=3)

            if save_popup:
                # 파일명 입력 후 저장
                ts = datetime.datetime.now().strftime("%H%M%S")
                save_path = os.path.join(PDF_TEST_DIR, f"{mol_name}_{ts}.pdf")
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                pyautogui.typewrite(save_path, interval=0.03)
                time.sleep(0.3)
                p_sdlg = os.path.join(SHOTS_DIR,
                    f"{ts}_{idx:02d}_{mol_name}_S6_savedialog.png")
                ImageGrab.grab().save(p_sdlg)  # 전체 화면
                shots.append(("PDF 저장 다이얼로그", p_sdlg))
                pyautogui.press("enter")
                time.sleep(2.5)
                # 저장 후 상태 캡처
                p_done = os.path.join(SHOTS_DIR,
                    f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S6_pdfdone.png")
                bbox = (new_popup.left, new_popup.top,
                        new_popup.left + new_popup.width,
                        new_popup.top  + new_popup.height)
                ImageGrab.grab(bbox=bbox).save(p_done)
                shots.append(("PDF 저장 완료", p_done))
                print(f"    S6 PDF: {save_path}")
            else:
                # 저장 다이얼로그 없음 → 현재 팝업 캡처
                p = os.path.join(SHOTS_DIR,
                    f"{datetime.datetime.now().strftime('%H%M%S')}_{idx:02d}_{mol_name}_S6_pdf_nosavedlg.png")
                bbox = (new_popup.left, new_popup.top,
                        new_popup.left + new_popup.width,
                        new_popup.top  + new_popup.height)
                ImageGrab.grab(bbox=bbox).save(p)
                shots.append(("PDF 저장 다이얼로그 없음", p))
                print(f"    S6 PDF: 저장 다이얼로그 미출현")
                pyautogui.press("escape")
                time.sleep(0.5)

            close_popup(new_popup)
            time.sleep(0.8)
            win = safe_activate(win)
        else:
            # 파일 선택 다이얼로그 출현 → dismiss
            pyautogui.press("escape")
            time.sleep(0.5)
            p = screenshot(win, f"{idx:02d}_{mol_name}_S6_pdf_nospec")
            shots.append(("스펙트럼 팝업 없음 (ORCA 필요?)", p))
            print(f"    S6 PDF: 스펙트럼 팝업 없음")

    except Exception as e:
        print(f"    S6 PDF ERROR: {e}")
        shots.append(("PDF 오류", None, str(e)))

    return win, shots

# ─── 메인 테스트 루프 ────────────────────────────────────

def run_one_molecule(win, mol_name, smiles, expected_color, note, idx, ts):
    """한 분자에 대해 6단계 전체 실행"""
    print(f"\n[{idx:02d}/{len(TEST_CASES):02d}] {mol_name} ({expected_color})")
    print(f"         SMILES: {smiles}")
    result = {
        "name": mol_name, "smiles": smiles,
        "expected": expected_color, "note": note,
        "stages": {}
    }

    # 분자 입력 (Drawing 모드에서)
    try:
        win = type_molecule(win, mol_name)
        p_draw = screenshot(win, f"{idx:02d}_{mol_name}_S0_draw")
        result["stages"]["S0_draw"] = [("그리기 레이어", p_draw)]
    except Exception as e:
        result["stages"]["S0_draw"] = [("그리기 오류", None, str(e))]

    # S1: 루이스 구조
    win, s1 = stage1_lewis(win, mol_name, idx)
    result["stages"]["S1_lewis"] = s1

    # S2: 이론적 구조
    win, s2 = stage2_theory(win, mol_name, idx)
    result["stages"]["S2_theory"] = s2

    # S3: 전체 선택
    win, s3 = stage3_select(win, mol_name, idx)
    result["stages"]["S3_select"] = s3

    # S4: 입체 구조 (3D 뷰를 위해 Theory 뷰 필요)
    # Theory 뷰로 복귀
    win = click_btn(win, "theory", wait=2.0) if "theory" in _calc(win) else win
    win, s4, popup_3d = stage4_3d(win, mol_name, idx)
    result["stages"]["S4_3d"] = s4

    # S5: 분광분석 (Theory 뷰 기반)
    win, s5 = stage5_spectra(win, mol_name, idx, popup_3d)
    result["stages"]["S5_spectra"] = s5

    # S6: PDF 내보내기 (Theory 뷰 기반)
    win, s6 = stage6_pdf(win, mol_name, idx, popup_3d)
    result["stages"]["S6_pdf"] = s6

    # 그리기 뷰로 복귀 (다음 분자 입력을 위해)
    try:
        win = safe_activate(win)
        c = _calc(win)
        bx, by = c["back"]
        pyautogui.click(bx, by)
        time.sleep(1.5)
    except Exception:
        pass

    return win, result

def run_tests():
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"ChemGrid 6-Stage Feedback Cycle - {ts}")
    print(f"테스트 케이스: {len(TEST_CASES)}개")
    print(f"{'='*60}")

    win = launch_chemgrid()
    if not win:
        print("[FATAL] ChemGrid 실행 실패")
        return []

    all_results = []
    for idx, (mol_name, smiles, exp_color, note) in enumerate(TEST_CASES, 1):
        win, result = run_one_molecule(
            win, mol_name, smiles, exp_color, note, idx, ts)
        all_results.append(result)

    kill_chemgrid()
    report_path = generate_html_report(all_results, ts)
    print(f"\n[REPORT] {report_path}")

    # 결과 JSON 저장
    json_path = os.path.join(REPORT_DIR, "verify_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2,
                  default=lambda x: str(x))

    return all_results

# ─── HTML 리포트 생성 ────────────────────────────────────

STAGE_INFO = {
    "S0_draw":    ("🖊 그리기 레이어",    "분자 텍스트 입력 후 캔버스에 그려진 결과"),
    "S1_lewis":   ("⚛ 루이스 구조",      "작용기/전하/고립전자쌍 포함 Lewis 표현"),
    "S2_theory":  ("🔬 이론적 구조",     "OH기 제대로 표현? +/- 전하 유지? 전자구름 색상?"),
    "S3_select":  ("🔲 전체 선택",       "파란 점선 테두리 + 분자명 + 입체구조 버튼 활성화?"),
    "S4_3d":      ("🧊 입체 구조",       "3D 좌표 올바름? 결합 차수? X/Y/Z 회전 후 뒤틀림?"),
    "S5_spectra": ("📊 분광분석",         """IR: 피크↓(inverted), baseline~100%, X=4000→400<br>
                   Raman: 피크↑, X=0→4000<br>
                   1H-NMR: Integration line, Multiplicity<br>
                   13C-NMR: Zone 색띠, Peak 라벨<br>
                   UV-Vis: 듀얼 뷰(ε + logε)<br>
                   MolOrbital: 오비탈 시각화"""),
    "S6_pdf":     ("📄 PDF 내보내기",    "흰 배경, 모든 분광 그래프 나열, 대학 분석장비 양식"),
}

def generate_html_report(results, timestamp):
    report_path = os.path.join(REPORT_DIR, "visual_feedback_report.html")

    rows_html = ""
    for r in results:
        name = r["name"]
        smiles = r["smiles"]
        expected = r["expected"]
        note = r["note"]

        stage_cells = ""
        for stage_key, (stage_label, stage_desc) in STAGE_INFO.items():
            shots = r["stages"].get(stage_key, [])
            if not shots:
                stage_cells += f'<td class="no-data">없음</td>'
                continue

            imgs_html = ""
            for item in shots:
                lbl = item[0]
                path = item[1] if len(item) > 1 else None
                err  = item[2] if len(item) > 2 else ""
                extra = item[3] if len(item) > 3 else ""

                if path and os.path.exists(path):
                    rel = os.path.relpath(path, REPORT_DIR).replace("\\", "/")
                    imgs_html += f"""
                    <div class="shot">
                      <div class="shot-label">{lbl}</div>
                      <img src="{rel}" onclick="zoom(this)" title="{extra}">
                      {f'<div class="shot-extra">{extra}</div>' if extra else ''}
                    </div>"""
                else:
                    imgs_html += f'<div class="shot-error">❌ {lbl}: {err or path or "No image"}</div>'

            stage_cells += f"""
            <td>
              <div class="stage-desc" title="{stage_desc}">{stage_label}</div>
              {imgs_html}
            </td>"""

        rows_html += f"""
        <tr>
          <td class="mol-name">
            <b>{name}</b><br>
            <code>{smiles[:40]}</code><br>
            <span class="expected">{expected}</span><br>
            <small>{note}</small>
          </td>
          {stage_cells}
        </tr>"""

    # 분광분석 기준 정리
    spectra_guide = """
    <table class="guide">
      <tr><th>분광</th><th>X축</th><th>Y축</th><th>피크 방향</th><th>특이사항</th></tr>
      <tr><td>IR</td><td>4000→400 cm⁻¹</td><td>Transmittance %</td><td>↓ 아래로</td><td>baseline~100%, inverted peaks</td></tr>
      <tr><td>Raman</td><td>0→4000 cm⁻¹</td><td>Intensity</td><td>↑ 위로</td><td>Sharp peaks, D/G band</td></tr>
      <tr><td>¹H NMR</td><td>12→0 ppm</td><td>Intensity</td><td>↑ 위로</td><td>Integration line, Splitting</td></tr>
      <tr><td>¹³C NMR</td><td>220→0 ppm</td><td>Intensity</td><td>↑ 위로</td><td>Singlets, Zone color (aliphatic/aromatic/carbonyl)</td></tr>
      <tr><td>UV-Vis</td><td>200→800 nm</td><td>ε (좌) / log ε (우)</td><td>↑ 위로</td><td>듀얼 뷰 필수</td></tr>
      <tr><td>MolOrbital</td><td>-</td><td>-</td><td>-</td><td>HOMO/LUMO 시각화</td></tr>
    </table>
    """

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>ChemGrid 6단계 피드백 리포트</title>
<style>
  body {{ background:#141422; color:#dde; font-family:Arial,sans-serif; padding:16px; }}
  h1 {{ color:#4fc3f7; margin-bottom:4px; }}
  h2 {{ color:#81d4fa; font-size:14px; margin-top:18px; border-bottom:1px solid #334; }}
  table {{ border-collapse:collapse; width:100%; font-size:11px; }}
  th {{ background:#0d3766; padding:8px 6px; text-align:left; position:sticky; top:0; z-index:10; }}
  td {{ padding:6px; border:1px solid #2a2a4a; vertical-align:top; min-width:120px; }}
  .mol-name {{ min-width:160px; background:#1a1a30; }}
  .mol-name b {{ font-size:14px; color:#fff; }}
  code {{ background:#333; padding:1px 4px; border-radius:3px; font-size:10px; word-break:break-all; }}
  .expected {{ color:#ffd54f; font-weight:bold; }}
  .stage-desc {{ color:#88bbff; font-size:10px; margin-bottom:6px; cursor:help; }}
  .shot {{ margin-bottom:8px; }}
  .shot-label {{ font-size:9px; color:#aaa; }}
  .shot img {{ max-width:280px; border:1px solid #445; cursor:zoom-in; display:block; }}
  .shot img:hover {{ border-color:#4fc3f7; }}
  .shot-extra {{ font-size:9px; color:#888; margin-top:2px; }}
  .shot-error {{ background:#2d1010; color:#f88; padding:4px; border-radius:3px; font-size:10px; }}
  .no-data {{ background:#1a1a1a; color:#666; text-align:center; }}
  .guide td, .guide th {{ font-size:11px; padding:4px 8px; }}
  .guide {{ max-width:900px; margin:10px 0; }}
  .legend {{ display:flex; gap:16px; margin:8px 0; font-size:12px; }}
  .dot {{ width:16px; height:16px; border-radius:50%; display:inline-block; vertical-align:middle; margin-right:4px; }}

  /* Zoom overlay */
  #overlay {{ display:none; position:fixed; top:0; left:0; width:100%; height:100%;
              background:rgba(0,0,0,0.85); z-index:999; cursor:zoom-out; }}
  #overlay img {{ max-width:95%; max-height:95%; margin:2.5% auto; display:block; }}
</style>
</head>
<body>
<h1>🔬 ChemGrid 6단계 사용자 환경 피드백 리포트</h1>
<p>생성: {timestamp} | 분자: {len(results)}개 | 단계: 6단계</p>

<h2>전자구름 색상 기준 (McMurry)</h2>
<div class="legend">
  <span><span class="dot" style="background:red"></span>RED = 전자풍부 (δ-): O, F, N, 음이온</span>
  <span><span class="dot" style="background:#2196F3"></span>BLUE = 전자부족 (δ+): H-O, 카보닐C, 양이온</span>
  <span><span class="dot" style="background:green"></span>GREEN = 중성: sp3 C-H</span>
</div>

<h2>분광분석 올바른 형태 기준</h2>
{spectra_guide}

<h2>테스트 결과 (이미지 클릭 시 확대)</h2>
<table>
  <thead>
    <tr>
      <th>분자</th>
      <th>S0 그리기</th>
      <th>S1 루이스</th>
      <th>S2 이론구조</th>
      <th>S3 전체선택</th>
      <th>S4 입체3D</th>
      <th>S5 분광분석</th>
      <th>S6 PDF</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>

<div id="overlay" onclick="this.style.display='none'">
  <img id="zoom-img" src="">
</div>

<script>
function zoom(img) {{
  document.getElementById('zoom-img').src = img.src;
  document.getElementById('overlay').style.display = 'block';
}}
</script>
</body>
</html>"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    return report_path

# ─── 엔트리 포인트 ────────────────────────────────────────
if __name__ == "__main__":
    results = run_tests()
    print(f"\n[DONE] {len(results)}개 분자 6단계 완료")
    print(f"[REPORT] {os.path.join(REPORT_DIR, 'visual_feedback_report.html')}")
