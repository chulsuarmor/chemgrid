"""
수정된 버튼 좌표로 이론적 구조 테스트
핵심: 이론적 구조 버튼은 하단 바 우측에 있음
"""
import time, os, base64
import win32gui, win32con
import pyautogui
import PIL.ImageGrab
import pyperclip

OUT = r'c:\chemgrid\docs\reports\theory_test'
os.makedirs(OUT, exist_ok=True)
imgs = []
pyautogui.FAILSAFE = False

def find_cg():
    wins = []
    def cb(hwnd, _):
        t = win32gui.GetWindowText(hwnd)
        if 'ChemGrid' in t and 'Visual Studio Code' not in t and win32gui.IsWindowVisible(hwnd):
            wins.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return wins[0] if wins else None

def focus():
    hwnd = find_cg()
    if not hwnd: return None
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    return win32gui.GetWindowRect(hwnd)

def shot(name, rect=None):
    if rect:
        L,T,R,B = rect
        img = PIL.ImageGrab.grab(bbox=(L,T,R,B))
    else:
        img = PIL.ImageGrab.grab()
    p = os.path.join(OUT, f'{name}.png')
    img.save(p)
    imgs.append((name, p))
    print(f'[SHOT] {name}')

def click_escape_all(L,T,R,B):
    """모든 팝업 닫기"""
    pyautogui.press('escape')
    time.sleep(0.2)
    pyautogui.press('escape')
    time.sleep(0.2)

# 창 찾기
rect = focus()
if not rect:
    print("ChemGrid 없음! Run_ChemGrid.bat 실행 필요")
    exit(1)
L,T,R,B = rect
W,H = R-L, B-T
print(f"창: {W}x{H} @ ({L},{T})")

# 좌표 정의 (실측 기반)
# 하단 바: 전자구름 표기 | [입력창] | → | 루이스 구조 | 이론적 구조
BOTTOM_Y = B - 28
INPUT_X = (L + R) // 2
THEORY_BTN = (R - 65, BOTTOM_Y)    # "이론적 구조"
LEWIS_BTN  = (R - 130, BOTTOM_Y)   # "루이스 구조"
DRAW_LAYER = (R - 195, BOTTOM_Y)   # 그리기 레이어로 (= 그리기 탭)

# 2번째 행 버튼들 (y ≈ T+63)
ROW2_Y = T + 63
CLEAR_BTN  = (L + 195, ROW2_Y)     # "전체 지우기"

print(f"THEORY_BTN: {THEORY_BTN}")
print(f"LEWIS_BTN: {LEWIS_BTN}")
print(f"CLEAR_BTN: {CLEAR_BTN}")
print(f"INPUT: ({INPUT_X}, {BOTTOM_Y})")

shot("init", rect)

# ─── 공통 초기화 함수 ─────────────────────
def clear_and_input(smiles_or_name, rect):
    L,T,R,B = rect
    click_escape_all(L,T,R,B)
    # 전체 지우기
    pyautogui.click(CLEAR_BTN[0], CLEAR_BTN[1])
    time.sleep(0.4)
    pyautogui.press('enter')  # 확인 다이얼로그
    time.sleep(0.5)
    # 입력창 클릭 → 클립보드 붙여넣기 → Enter
    pyperclip.copy(smiles_or_name)
    pyautogui.click(INPUT_X, BOTTOM_Y)
    time.sleep(0.4)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(2.5)

def go_theory(rect):
    pyautogui.click(THEORY_BTN[0], THEORY_BTN[1])
    time.sleep(2.0)

# ──────────────────────────────────────────
print("\n=== TEST 1: benzene 이론적 구조 ===")
rect = focus()
clear_and_input('benzene', rect)
shot("benzene_draw", rect)
go_theory(rect)
shot("benzene_theory", rect)

print("\n=== TEST 2: Cp⁻ 이론적 구조 (핵심!) ===")
rect = focus()
clear_and_input('[cH-]1cccc1', rect)
shot("cp_draw", rect)
go_theory(rect)
shot("cp_theory_AFTER_FIX", rect)  # 핵심 검증 이미지

print("\n=== TEST 3: tropylium 양이온 ===")
rect = focus()
clear_and_input('[cH+]1cccccc1', rect)
shot("tropylium_draw", rect)
go_theory(rect)
shot("tropylium_theory", rect)

print("\n=== TEST 4: 텍스트 입력 다양성 ===")
for name, expected in [
    ('aspirin', '아스피린 구조'),
    ('CH3COOH', '아세트산'),
    ('naphthalene', '나프탈렌'),
]:
    rect = focus()
    clear_and_input(name, rect)
    shot(f"text_{name.replace('/', '_')}_draw", rect)
    go_theory(rect)
    shot(f"text_{name.replace('/', '_')}_theory", rect)

# HTML 보고서
print("\n=== 보고서 생성 ===")
html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>Theory Test</title>',
        '<style>body{background:#0d1520;color:#eee;font-family:sans-serif;padding:15px}',
        '.box{margin:15px 0;padding:10px;border-radius:6px;border:2px solid #333}',
        '.KEY{border-color:#0f0;background:#001800}',
        'img{max-width:100%;display:block;margin:6px 0}h3{color:#7af}</style></head><body>',
        '<h1>ChemGrid Theory Layer Test (수정 후)</h1>',
        '<h2 style="color:#0f0">🔑 핵심: cp_theory_AFTER_FIX = 5탄소 균일 전자구름?</h2>']
for name, path in imgs:
    is_key = 'AFTER_FIX' in name or 'tropylium_theory' in name or 'benzene_theory' in name
    cls = 'box KEY' if is_key else 'box'
    if os.path.exists(path):
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        html.append(f'<div class="{cls}"><h3>{"🔑 " if is_key else ""}{name}</h3>')
        html.append(f'<img src="data:image/png;base64,{b64}"></div>')
html.append('</body></html>')
out = r'c:\chemgrid\docs\reports\theory_test.html'
with open(out, 'w', encoding='utf-8') as f:
    f.write(''.join(html))
print(f'완료: {out} ({len(imgs)}개 이미지)')
