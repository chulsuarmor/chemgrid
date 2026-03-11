"""
개선된 ChemGrid 시각 테스트
- win32gui로 창 포커스 확실히
- 클립보드 붙여넣기 (typewrite 대신) 
- ChemGrid 창만 캡처 (Chrome Remote Desktop 제외)
- PNG 내보내기 기능 직접 활용
"""
import time, os, sys, base64
import win32gui, win32con
import pyautogui
import PIL.ImageGrab
import pyperclip

OUT_DIR = r'c:\chemgrid\docs\reports\proper_test'
os.makedirs(OUT_DIR, exist_ok=True)
results = []

pyautogui.FAILSAFE = False

def find_cg_hwnd():
    wins = []
    def cb(hwnd, _):
        t = win32gui.GetWindowText(hwnd)
        if 'ChemGrid' in t and 'Visual Studio Code' not in t and win32gui.IsWindowVisible(hwnd):
            wins.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return wins[0][0] if wins else None

def get_rect():
    hwnd = find_cg_hwnd()
    if not hwnd: return None
    return win32gui.GetWindowRect(hwnd)  # (L, T, R, B)

def focus_cg():
    hwnd = find_cg_hwnd()
    if not hwnd:
        print("ERROR: ChemGrid 창 없음"); return False
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(1.0)
    return True

def shot(name):
    rect = get_rect()
    if rect:
        L, T, R, B = rect
        img = PIL.ImageGrab.grab(bbox=(L, T, R, B))
    else:
        img = PIL.ImageGrab.grab()
    path = os.path.join(OUT_DIR, f"{name}.png")
    img.save(path)
    results.append((name, path))
    print(f"  [SHOT] {name}")
    return path

def paste_text(text, input_x, input_y):
    """클립보드로 안전 입력 (typewrite 대신)"""
    pyperclip.copy(text)
    pyautogui.click(input_x, input_y)
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(2.5)  # 분자 생성 대기

def get_coords():
    """창 크기 기반 버튼 좌표 계산"""
    rect = get_rect()
    if not rect: return None
    L, T, R, B = rect
    W, H = R - L, B - T
    return {
        'L': L, 'T': T, 'R': R, 'B': B, 'W': W, 'H': H,
        # 텍스트 입력창 (하단)
        'input': (L + W // 2, B - 28),
        # 전체 지우기 버튼 (상단 2번째 줄)
        'clear': (L + 200, T + 48),
        # 레이어 탭들 (상단에서 약 65px)
        'tab_draw': (L + int(W * 0.06), T + 65),
        'tab_lewis': (L + int(W * 0.12), T + 65),
        'tab_theory': (L + int(W * 0.20), T + 65),
        # 3D 버튼 (오른쪽 하단 패널)
        'btn_3d': (R - 120, B - 50),
        # IR/NMR/UV 버튼 (오른쪽)
        'btn_ir': (R - 200, T + 65),
        'btn_nmr_h': (R - 150, T + 65),
        'btn_uvvis': (R - 100, T + 65),
    }

# ──────────────────────────────────────────────
print("=== 개선된 ChemGrid 시각 테스트 ===")

# ChemGrid 실행 확인
hwnd = find_cg_hwnd()
if not hwnd:
    print("ChemGrid 없음, 실행 중...")
    import subprocess
    subprocess.Popen(['Start-Process', 'cmd', '-ArgumentList', '/c Run_ChemGrid.bat'],
                     shell=True, cwd='c:/chemgrid')
    time.sleep(5)
    hwnd = find_cg_hwnd()
    if not hwnd:
        print("실패: ChemGrid 시작 불가"); sys.exit(1)

focus_cg()
rect = get_rect()
L, T, R, B = rect
W, H = R-L, B-T
print(f"창 크기: {W}x{H}")

# 창 최대화 후 초기 스크린샷
shot("00_initial")

# 좌표 계산
c = get_coords()
print(f"입력창: {c['input']}, 지우기: {c['clear']}")

# ─── 테스트 A: 창 레이아웃 탐색 ───────────
# 창 상단 바 캡처해서 버튼 위치 확인
shot("A0_toolbar_check")

# ─── 테스트 1: benzene 입력 → 그리기 레이어 ───
print("\n[TEST 1] benzene 입력")
focus_cg()
# 전체 지우기 (상단 2번째 줄)
pyautogui.click(c['clear'])
time.sleep(0.5)
pyautogui.press('enter')
time.sleep(0.5)
shot("01a_cleared")

# 입력창에 benzene 입력 (클립보드 방식)
paste_text('benzene', c['input'][0], c['input'][1])
shot("01b_benzene_draw")

# 이론적 구조 탭 클릭 (여러 위치 시도)
for tab_y in [65, 100, 130]:
    pyautogui.click(L + int(W * 0.20), T + tab_y)
    time.sleep(0.3)
shot("01c_benzene_theory_attempt")
time.sleep(1.5)
shot("01d_benzene_theory")

# ─── 테스트 2: Cp⁻ 이론적 구조 전자구름 ───
print("\n[TEST 2] Cp⁻ 전자구름 균일 분포 테스트")
focus_cg()
# 그리기 레이어로 돌아가기
for tab_y in [65, 100, 130]:
    pyautogui.click(L + int(W * 0.06), T + tab_y)
    time.sleep(0.3)
time.sleep(0.5)

# 전체 지우기
pyautogui.click(c['clear'])
time.sleep(0.5)
pyautogui.press('enter')
time.sleep(0.5)

# Cp⁻ SMILES 입력
paste_text('[cH-]1cccc1', c['input'][0], c['input'][1])
shot("02a_cp_draw")

# 이론적 구조 탭
for tab_y in [65, 100, 130]:
    pyautogui.click(L + int(W * 0.20), T + tab_y)
    time.sleep(0.3)
time.sleep(2.0)
shot("02b_cp_theory_after_fix")

# ─── 테스트 3: tropylium 양이온 ───
print("\n[TEST 3] tropylium 양이온")
focus_cg()
for tab_y in [65, 100]:
    pyautogui.click(L + int(W * 0.06), T + tab_y)
    time.sleep(0.3)
time.sleep(0.5)
pyautogui.click(c['clear'])
time.sleep(0.5)
pyautogui.press('enter')
time.sleep(0.5)
paste_text('[cH+]1cccccc1', c['input'][0], c['input'][1])
shot("03a_tropylium_draw")
for tab_y in [65, 100]:
    pyautogui.click(L + int(W * 0.20), T + tab_y)
    time.sleep(0.3)
time.sleep(2.0)
shot("03b_tropylium_theory")

# ─── 테스트 4: 다양한 텍스트 입력 ───
print("\n[TEST 4] 다양한 분자 입력 테스트")
test_mols = [
    ('CH3COOH', 'acetic_acid'),
    ('aspirin', 'aspirin'),
    ('CH3CH2OH', 'ethanol'),
    ('naphthalene', 'naphthalene'),
]

for mol_input, mol_name in test_mols:
    focus_cg()
    for tab_y in [65, 100]:
        pyautogui.click(L + int(W * 0.06), T + tab_y)
        time.sleep(0.2)
    time.sleep(0.3)
    pyautogui.click(c['clear'])
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(0.3)
    paste_text(mol_input, c['input'][0], c['input'][1])
    shot(f"04_{mol_name}_draw")
    for tab_y in [65, 100]:
        pyautogui.click(L + int(W * 0.20), T + tab_y)
        time.sleep(0.3)
    time.sleep(1.5)
    shot(f"04_{mol_name}_theory")

# ─── 테스트 5: 분광분석 ───
print("\n[TEST 5] 분광분석 (benzene)")
focus_cg()
for tab_y in [65, 100]:
    pyautogui.click(L + int(W * 0.06), T + tab_y)
    time.sleep(0.2)
pyautogui.click(c['clear'])
time.sleep(0.3)
pyautogui.press('enter')
time.sleep(0.3)
paste_text('benzene', c['input'][0], c['input'][1])

# 이론적 구조로 전환
for tab_y in [65, 100]:
    pyautogui.click(L + int(W * 0.20), T + tab_y)
    time.sleep(0.3)
time.sleep(1.5)
shot("05a_benzene_theory_pre_spectra")

# 전체 선택 후 스펙트럼 클릭
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.5)
# IR 버튼 (다양한 위치 탐색)
for ix in [0.42, 0.50, 0.58, 0.65]:
    pyautogui.click(L + int(W * ix), T + 65)
    time.sleep(0.3)
shot("05b_spectra_area")
time.sleep(1.5)
shot("05c_after_spectra_click")

# ─── HTML 보고서 생성 ───
print("\n=== HTML 보고서 생성 ===")
html = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
        '<title>ChemGrid 개선 테스트</title>',
        '<style>body{font-family:sans-serif;background:#0d0d1e;color:#eee;padding:15px}',
        '.box{margin:15px 0;border:1px solid #333;padding:10px;border-radius:6px}',
        'img{max-width:900px;border:1px solid #555;display:block;margin:8px 0}',
        'h3{color:#7af;margin:5px 0}',
        '.note{background:#1a2a1a;border:1px solid #2a5a2a;padding:8px;margin:10px 0;border-radius:4px}',
        '</style></head><body>',
        '<h1>ChemGrid 개선 테스트 - 수정 후</h1>',
        '<div class="note"><b>핵심 확인:</b> 02b_cp_theory_after_fix → Cp⁻ 5탄소 균일 전자구름?</div>']

for name, path in results:
    if os.path.exists(path):
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        html.append(f'<div class="box"><h3>{name}</h3>')
        html.append(f'<img src="data:image/png;base64,{b64}"></div>')

html.append('</body></html>')
rpt = r'c:\chemgrid\docs\reports\proper_test.html'
with open(rpt, 'w', encoding='utf-8') as f:
    f.write(''.join(html))
print(f'보고서: {rpt} ({len(results)}개 이미지)')
