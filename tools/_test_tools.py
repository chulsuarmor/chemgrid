"""
ChemGrid Arrow/Text/Load 정밀 테스트
- Arrow 도구 직접 클릭 → 화살표 드래그
- Text 도구 직접 클릭 → 텍스트 입력
- Ctrl+O로 .chem 파일 로드
- 줌인/줌아웃
"""
import subprocess, time, sys, os, math, ctypes
from ctypes import wintypes

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.15

ss_idx = 0
def ss(name):
    global ss_idx
    ss_idx += 1
    f = os.path.join(r"c:\chemgrid", f"_tt_{ss_idx:02d}_{name}.png")
    pyautogui.screenshot(f)
    print(f"[SS] {f}")

def find_window(title_part):
    EnumWindows = ctypes.windll.user32.EnumWindows
    GetWindowTextW = ctypes.windll.user32.GetWindowTextW
    SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow
    ShowWindow = ctypes.windll.user32.ShowWindow
    GetWindowRect = ctypes.windll.user32.GetWindowRect
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    found = [None]
    def cb(hwnd, lp):
        buf = ctypes.create_unicode_buffer(256)
        GetWindowTextW(hwnd, buf, 256)
        if title_part in buf.value:
            found[0] = hwnd
            return False
        return True
    EnumWindows(WNDENUMPROC(cb), 0)
    if found[0]:
        ShowWindow(found[0], 9)
        SetForegroundWindow(found[0])
        r = wintypes.RECT()
        GetWindowRect(found[0], ctypes.byref(r))
        return (r.left, r.top, r.right, r.bottom)
    return None

print("=" * 50)
print("Arrow/Text/Load 정밀 테스트")
print("=" * 50)

# 앱 실행
proc = subprocess.Popen(
    ["python", "draw.py"],
    cwd=r"c:\chemgrid\agents\10_testing_build\integrated",
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
)
time.sleep(5)

rect = find_window("ChemGrid")
if not rect:
    print("ERROR: 창 못찾음!")
    err = proc.stderr.read().decode('utf-8', errors='replace')
    print(f"STDERR:\n{err[:1500]}")
    sys.exit(1)

L, T, R, B = rect
W, H = R - L, B - T
print(f"창: ({L},{T})-({R},{B}), {W}x{H}")

# 툴바 y좌표 (타이틀바 30px + 약간)
tb_y = T + 55  # 툴바 아이콘 중심 y좌표 (타이틀바 + 메뉴바 고려)

# 툴바 아이콘 순서: Select, Hand, Bond, Arrow, Pen, Text, Eraser
# 각 아이콘 ~26px 폭, 시작 x = L + 40 쯤
icon_start_x = L + 40
icon_width = 26

def toolbar_x(idx):
    return icon_start_x + idx * icon_width

# 인덱스: 0=Select, 1=Hand, 2=Bond, 3=Arrow, 4=Pen, 5=Text, 6=Eraser
ARROW_IDX = 3
TEXT_IDX = 5

# 캔버스 중심
cx = L + W // 2
cy = T + 120 + (H - 120) // 2

ss("00_launched")
time.sleep(0.5)

# ===== 테스트 1: Arrow 도구 =====
print("\n[1] Arrow 도구 테스트...")
arrow_x = toolbar_x(ARROW_IDX)
print(f"   Arrow 버튼 좌표: ({arrow_x}, {tb_y})")
pyautogui.click(arrow_x, tb_y)
time.sleep(0.5)
ss("01_arrow_selected")

# 화살표 드래그: 캔버스 중앙에서 오른쪽으로
a_start_x, a_start_y = cx - 100, cy - 50
a_end_x, a_end_y = cx + 100, cy - 50
print(f"   화살표 드래그: ({a_start_x},{a_start_y}) -> ({a_end_x},{a_end_y})")
pyautogui.moveTo(a_start_x, a_start_y)
time.sleep(0.2)
pyautogui.mouseDown()
time.sleep(0.1)
pyautogui.moveTo(a_end_x, a_end_y, duration=0.5)
time.sleep(0.1)
pyautogui.mouseUp()
time.sleep(0.5)
ss("02_arrow_drawn")

# ===== 테스트 2: Text 도구 =====
print("\n[2] Text 도구 테스트...")
text_x = toolbar_x(TEXT_IDX)
print(f"   Text 버튼 좌표: ({text_x}, {tb_y})")
pyautogui.click(text_x, tb_y)
time.sleep(0.5)
ss("03_text_selected")

# 텍스트 상자 생성
t_pos_x, t_pos_y = cx, cy + 50
print(f"   텍스트 위치: ({t_pos_x},{t_pos_y})")
pyautogui.click(t_pos_x, t_pos_y)
time.sleep(0.3)

# 텍스트 입력
pyautogui.typewrite("CH_3OH", interval=0.05)
time.sleep(0.5)
ss("04_text_typed")

# Enter로 편집 종료
pyautogui.press('enter')
time.sleep(0.3)

# ===== 테스트 3: Bond 도구로 돌아가서 결합 그리기 =====
print("\n[3] Bond 도구로 전환 후 결합 그리기...")
bond_x = toolbar_x(2)  # Bond = index 2
pyautogui.click(bond_x, tb_y)
time.sleep(0.3)

# 간단한 결합 3개 (지그재그)
gs = 40
bx, by = cx - 60, cy - 120
for i in range(3):
    sx = bx + i * gs
    sy = by + (0 if i % 2 == 0 else -gs * 0.866)
    ex = bx + (i + 1) * gs
    ey = by + (0 if (i + 1) % 2 == 0 else -gs * 0.866)
    pyautogui.moveTo(sx, sy)
    pyautogui.mouseDown()
    time.sleep(0.05)
    pyautogui.moveTo(ex, ey, duration=0.15)
    pyautogui.mouseUp()
    time.sleep(0.15)

ss("05_bonds_after_text")

# ===== 테스트 4: 줌인/줌아웃 =====
print("\n[4] 줌인/줌아웃 테스트...")
pyautogui.moveTo(cx, cy)
time.sleep(0.2)
for _ in range(5):
    pyautogui.scroll(3, cx, cy)
    time.sleep(0.15)
ss("06_zoom_in")
for _ in range(10):
    pyautogui.scroll(-3, cx, cy)
    time.sleep(0.15)
ss("07_zoom_out")
for _ in range(5):
    pyautogui.scroll(3, cx, cy)
    time.sleep(0.15)

# ===== 테스트 5: 루이스 구조 버튼 =====
print("\n[5] 루이스 구조 버튼 테스트...")
# 하단 버튼들: "전자구름 끄기" | "루이스 구조" | "이론적 구조"
lewis_btn_x = R - 190
lewis_btn_y = B - 25
print(f"   루이스 버튼 좌표: ({lewis_btn_x},{lewis_btn_y})")
pyautogui.click(lewis_btn_x, lewis_btn_y)
time.sleep(2)
ss("08_lewis_clicked")

# 돌아가기
back_x = R - 100
back_y = B - 25
pyautogui.click(back_x, back_y)
time.sleep(2)
ss("09_back_from_lewis")

# ===== 테스트 6: Ctrl+O 파일 로드 =====
print("\n[6] Ctrl+O 파일 로드 테스트...")
# 먼저 전체 지우기
pyautogui.hotkey('ctrl', 'a')
time.sleep(0.2)
pyautogui.press('delete')
time.sleep(0.3)

pyautogui.hotkey('ctrl', 'o')
time.sleep(2)
ss("10_open_dialog")

# 파일 경로 입력
pyautogui.typewrite(r"c:\chemgrid\_source\1.chem", interval=0.02)
time.sleep(0.5)
pyautogui.press('enter')
time.sleep(2)
ss("11_file_loaded")

# ===== 완료 =====
print("\n" + "=" * 50)
print(f"테스트 완료! {ss_idx}개 스크린샷")
print("=" * 50)

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
