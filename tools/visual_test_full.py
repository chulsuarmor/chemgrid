"""
ChemGrid 전수 시각 테스트 스크립트
- 전자구름 편재화 수정 확인 (Cp-, tropylium)
- 이론적 구조 방향족 결합 표기 확인
- 텍스트 입력 다양한 분자명 테스트
- 분광분석 전수점검
"""
import time, os, base64
from PIL import ImageGrab
import pygetwindow as gw
import pyautogui

pyautogui.FAILSAFE = False
SAVE_DIR = r"c:\chemgrid\docs\reports\visual_test_full"
os.makedirs(SAVE_DIR, exist_ok=True)
screenshots = []

def find_cg():
    for w in gw.getAllWindows():
        if 'ChemGrid' in w.title and 'Visual Studio Code' not in w.title and w.width > 300:
            return w
    return None

def shot(name):
    w = find_cg()
    if w:
        img = ImageGrab.grab(bbox=(w.left, w.top, w.left+w.width, w.top+w.height))
    else:
        img = ImageGrab.grab()
    path = os.path.join(SAVE_DIR, f"{name}.png")
    img.save(path)
    screenshots.append((name, path))
    print(f"[SHOT] {name}")
    return path

def wait_for_cg(timeout=15):
    for _ in range(timeout*2):
        w = find_cg()
        if w and w.width > 300:
            try: w.activate()
            except: pass
            time.sleep(0.5)
            return w
        time.sleep(0.5)
    return None

def click_in_cg(rel_x_ratio, rel_y_ratio):
    """창 내 상대 좌표로 클릭"""
    w = find_cg()
    if not w: return
    x = int(w.left + w.width * rel_x_ratio)
    y = int(w.top + w.height * rel_y_ratio)
    pyautogui.click(x, y)
    time.sleep(0.3)

def type_mol(name_str):
    """텍스트 입력창에 분자명 입력 후 Enter"""
    w = find_cg()
    if not w: return
    # 입력창: 창 하단에서 약 40px 위, 중앙 정도
    ix = w.left + w.width // 2 - 50
    iy = w.top + w.height - 45
    pyautogui.click(ix, iy)
    time.sleep(0.3)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)
    pyautogui.typewrite(name_str, interval=0.05)
    time.sleep(0.2)
    pyautogui.press('enter')
    time.sleep(1.5)

def click_btn(btn_name):
    """버튼 이름으로 클릭 (pyautogui locateOnScreen은 미사용, 좌표 기반)"""
    w = find_cg()
    if not w: return
    # 버튼 위치는 툴바에 있음 - 상단에서 약 35px 아래
    # 각 버튼 위치 추정 (상단 왼쪽부터 순서)
    btn_map = {
        'theory': (w.left + int(w.width * 0.18), w.top + 35),
        'draw':   (w.left + int(w.width * 0.06), w.top + 35),
        '3d':     (w.left + int(w.width * 0.30), w.top + 35),
        'ir':     (w.left + int(w.width * 0.42), w.top + 35),
        'nmr_h':  (w.left + int(w.width * 0.50), w.top + 35),
        'nmr_c':  (w.left + int(w.width * 0.58), w.top + 35),
        'uvvis':  (w.left + int(w.width * 0.66), w.top + 35),
        'pdf':    (w.left + int(w.width * 0.90), w.top + 35),
    }
    if btn_name in btn_map:
        pyautogui.click(*btn_map[btn_name])
        time.sleep(1.5)

# ──────────────────────────────────────────────────────────
print("=== ChemGrid 전수 시각 테스트 시작 ===")
print("ChemGrid 창 대기 중...")
w = wait_for_cg(20)

if not w:
    print("ERROR: ChemGrid 창을 찾을 수 없음!")
    exit(1)

print(f"ChemGrid 창 발견: {w.title} {w.width}x{w.height}")
shot("00_initial_state")

# ── 테스트 1: benzene 입력 → 그리기 레이어 ──
print("\n[TEST 1] benzene 입력")
type_mol("benzene")
shot("01_benzene_drawing")

# 이론적 구조 버튼 클릭
click_btn('theory')
shot("02_benzene_theory")

# ── 테스트 2: cp- 입력 → 이론적 구조 전자구름 ──
print("\n[TEST 2] cyclopentadienyl anion")
click_btn('draw')
time.sleep(0.3)
type_mol("[cH-]1cccc1")
shot("03_cp_drawing")
click_btn('theory')
shot("04_cp_theory_electron_cloud")

# ── 테스트 3: 다양한 텍스트 입력 테스트 ──
molecules_to_test = [
    ("CH3COOH", "05_acetic_acid"),
    ("aspirin", "06_aspirin"),
    ("CH3CH2OH", "07_ethanol"),
    ("caffeine", "08_caffeine"),
]
for mol_name, shot_name in molecules_to_test:
    print(f"\n[TEST] {mol_name}")
    click_btn('draw')
    time.sleep(0.3)
    type_mol(mol_name)
    shot(shot_name + "_draw")
    click_btn('theory')
    shot(shot_name + "_theory")

# ── 테스트 4: 분광분석 - benzene ──
print("\n[TEST 4] 분광분석 전수점검 (benzene)")
click_btn('draw')
time.sleep(0.3)
type_mol("benzene")
shot("09_benzene_for_spectra")

# IR
click_btn('ir')
shot("10_ir_spectrum")
pyautogui.press('escape')
time.sleep(0.5)

# NMR H1
click_btn('nmr_h')
shot("11_nmr_h_spectrum")
pyautogui.press('escape')
time.sleep(0.5)

# NMR C13
click_btn('nmr_c')
shot("12_nmr_c_spectrum")
pyautogui.press('escape')
time.sleep(0.5)

# UV-Vis
click_btn('uvvis')
shot("13_uvvis_spectrum")
pyautogui.press('escape')
time.sleep(0.5)

# ── 테스트 5: 이론적 구조에서 선택 → 3D ──
print("\n[TEST 5] 이론적 구조 선택 → 3D 팝업")
click_btn('theory')
time.sleep(0.5)
# 캔버스 전체 드래그 선택
w2 = find_cg()
if w2:
    cx = w2.left + w2.width//2
    cy = w2.top + w2.height//2
    pyautogui.moveTo(w2.left + 50, w2.top + 100)
    pyautogui.dragTo(w2.left + w2.width - 50, w2.top + w2.height - 80, duration=0.5, button='left')
    time.sleep(0.5)
    shot("14_theory_selection")
    click_btn('3d')
    shot("15_3d_popup")
    pyautogui.press('escape')

# ── HTML 리포트 생성 ──
print("\n=== HTML 리포트 생성 ===")
html_parts = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
              '<title>ChemGrid 전수 시각 테스트</title>',
              '<style>body{font-family:sans-serif;background:#1a1a2e;color:#eee;padding:20px}',
              '.test-item{margin:20px 0;border:1px solid #444;padding:15px;border-radius:8px}',
              'img{max-width:900px;border:2px solid #555;display:block;margin:10px 0}</style></head><body>',
              f'<h1>ChemGrid 전수 시각 테스트 결과</h1>']

for name, path in screenshots:
    if os.path.exists(path):
        with open(path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        html_parts.append(f'<div class="test-item"><h3>{name}</h3>'
                         f'<img src="data:image/png;base64,{b64}"></div>')

html_parts.append('</body></html>')
report_path = r"c:\chemgrid\docs\reports\visual_test_full.html"
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(html_parts))

print(f"리포트 저장: {report_path}")
print(f"총 {len(screenshots)}개 스크린샷")
