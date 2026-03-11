"""
ChemGrid 소스 파일 로드 + 복합 테스트
1. _source/*.chem 파일을 프로그래밍적으로 로드
2. 팔각고리 직접 그리기
3. 루이스 구조 전환
4. RS 이성질체 예시 확인
"""
import subprocess, time, sys, os, math, json, ctypes
from ctypes import wintypes

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.12

ss_idx = 0
def ss(name):
    global ss_idx
    ss_idx += 1
    f = os.path.join(r"c:\chemgrid", f"_src_{ss_idx:02d}_{name}.png")
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

# ===== 소스 파일 분석 =====
print("=" * 50)
print("소스 파일 분석")
print("=" * 50)
source_dir = r"c:\chemgrid\_source"
chem_files = sorted([f for f in os.listdir(source_dir) if f.endswith('.chem')])
for cf in chem_files:
    path = os.path.join(source_dir, cf)
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    n_atoms = len(data.get("atoms", {}))
    n_bonds = len(data.get("bonds", {}))
    # 원소 종류 추출
    elements = set()
    for k, v in data.get("atoms", {}).items():
        main = v.get("main", "")
        if main:
            elements.add(main)
    elem_str = ",".join(sorted(elements)) if elements else "C만"
    print(f"  {cf}: 원자 {n_atoms}개, 결합 {n_bonds}개, 원소: {elem_str}")

# ===== 앱 실행 =====
print("\n앱 실행...")
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

tb_y = T + 55
icon_start_x = L + 40
icon_width = 26
cx = L + W // 2
cy = T + 120 + (H - 120) // 2

def toolbar_x(idx):
    return icon_start_x + idx * icon_width

ss("00_launched")

# ===== 테스트 1: 팔각고리 직접 그리기 =====
print("\n[1] 팔각고리 (8각형) 그리기...")
# Bond 도구 선택 (인덱스 2)
pyautogui.click(toolbar_x(2), tb_y)
time.sleep(0.3)

# 팔각형 꼭짓점 (그리드 스냅 기대)
oct_cx, oct_cy = cx, cy
oct_r = 70  # 반지름
oct_pts = []
for i in range(8):
    angle = math.radians(90 + 45 * i)
    x = oct_cx + math.cos(angle) * oct_r
    y = oct_cy - math.sin(angle) * oct_r
    oct_pts.append((int(x), int(y)))

# 8개 변을 드래그로 그리기
for i in range(8):
    x1, y1 = oct_pts[i]
    x2, y2 = oct_pts[(i + 1) % 8]
    pyautogui.moveTo(x1, y1)
    time.sleep(0.05)
    pyautogui.mouseDown()
    time.sleep(0.05)
    pyautogui.moveTo(x2, y2, duration=0.15)
    pyautogui.mouseUp()
    time.sleep(0.15)

ss("01_octagon_drawn")

# ===== 테스트 2: 루이스 구조 전환 =====
print("\n[2] 팔각고리 → 루이스 구조 전환...")
lewis_btn_x = R - 190
lewis_btn_y = B - 25
pyautogui.click(lewis_btn_x, lewis_btn_y)
time.sleep(2.5)
ss("02_octagon_lewis")

# 돌아가기
back_x = R - 100
back_y = B - 25
pyautogui.click(back_x, back_y)
time.sleep(2)

# ===== 테스트 3: 전체 지우기 후 _source/1.chem 프로그래밍 로드 =====
print("\n[3] 전체 지우기 + 소스 파일 1.chem 프로그래밍 로드...")
# 저장/불러오기 버튼을 통해 로드해야 함
# 메뉴에서 '파일' → '불러오기' 사용
# 또는 '저장/불러오기' 드롭다운 버튼 찾기

# 먼저 현재 그림 전체 지우기: Select All + Delete
pyautogui.click(toolbar_x(0), tb_y)  # Select 도구
time.sleep(0.2)
# 전체 영역 드래그 선택
pyautogui.moveTo(L + 40, T + 100)
pyautogui.mouseDown()
pyautogui.moveTo(R - 40, B - 60, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.2)
pyautogui.press('delete')
time.sleep(0.3)

# 저장/불러오기 버튼 찾기 - 툴바 우측 끝 영역
# 스크린샷에서 확인한 위치 (기존 스크린샷 기준 우상단)
# 다른 방법: 메뉴바의 "파일" 메뉴 사용
# toolbar_setup.py에서 "file_menu" 및 "저장/불러오기" 버튼 확인됨
# 보통 툴바 우측 끝에 위치

# 직접 파일 경로로 로드하는 Python 명령 전달 (socket이나 stdin 불가)
# 대신 pyautogui로 메뉴바 → 파일 클릭
# 아이콘 목록 끝부분 (세이브 아이콘)
save_btn_x = R - 60  # 저장/불러오기 버튼 대략적 위치
save_btn_y = tb_y
pyautogui.click(save_btn_x, save_btn_y)
time.sleep(1)
ss("03_save_menu_open")

# 메뉴가 열렸으면 "불러오기" 클릭 (보통 두 번째 항목)
pyautogui.click(save_btn_x, save_btn_y + 55)  # 불러오기 항목
time.sleep(2)
ss("04_load_dialog")

# 파일 경로 입력 (Windows 파일 다이얼로그)
# 파일명 입력 필드에 경로 타이핑
pyautogui.typewrite(r"c:\chemgrid\_source\1.chem", interval=0.01)
time.sleep(0.3)
pyautogui.press('enter')
time.sleep(2)
ss("05_source1_loaded")

# ===== 테스트 4: 줌아웃해서 전체 구조 보기 =====
print("\n[4] 줌아웃으로 전체 구조 확인...")
pyautogui.moveTo(cx, cy)
for _ in range(8):
    pyautogui.scroll(-3, cx, cy)
    time.sleep(0.15)
ss("06_source1_zoomed_out")

# ===== 테스트 5: 루이스 구조 전환 =====
print("\n[5] source1 → 루이스 구조 전환...")
pyautogui.click(lewis_btn_x, lewis_btn_y)
time.sleep(2.5)
ss("07_source1_lewis")

# 이론적 구조
theory_btn_x = R - 70
theory_btn_y = B - 25
pyautogui.click(theory_btn_x, theory_btn_y)
time.sleep(2.5)
ss("08_source1_theory")

# 돌아가기
pyautogui.click(back_x, back_y)
time.sleep(2)

# ===== 테스트 6: 칠각고리 (7각형) 그리기 =====
print("\n[6] 칠각고리 (7각형) 그리기...")
# 먼저 전체 지우기
pyautogui.click(toolbar_x(0), tb_y)  # Select
time.sleep(0.2)
pyautogui.moveTo(L + 40, T + 100)
pyautogui.mouseDown()
pyautogui.moveTo(R - 40, B - 60, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.2)
pyautogui.press('delete')
time.sleep(0.3)

# Bond 도구
pyautogui.click(toolbar_x(2), tb_y)
time.sleep(0.2)

# 칠각형
hept_pts = []
for i in range(7):
    angle = math.radians(90 + 360/7 * i)
    x = cx + math.cos(angle) * 80
    y = cy - math.sin(angle) * 80
    hept_pts.append((int(x), int(y)))

for i in range(7):
    x1, y1 = hept_pts[i]
    x2, y2 = hept_pts[(i + 1) % 7]
    pyautogui.moveTo(x1, y1)
    time.sleep(0.05)
    pyautogui.mouseDown()
    time.sleep(0.05)
    pyautogui.moveTo(x2, y2, duration=0.15)
    pyautogui.mouseUp()
    time.sleep(0.15)

ss("09_heptagon")

# 루이스 전환
pyautogui.click(lewis_btn_x, lewis_btn_y)
time.sleep(2.5)
ss("10_heptagon_lewis")

# 돌아가기
pyautogui.click(back_x, back_y)
time.sleep(2)

# ===== 테스트 7: 화살표 + 텍스트 조합 =====
print("\n[7] 화살표 + 텍스트 조합 테스트...")
# Arrow 도구
pyautogui.click(toolbar_x(3), tb_y)
time.sleep(0.3)

# 화살표 1: 오른쪽
pyautogui.moveTo(cx + 120, cy)
pyautogui.mouseDown()
pyautogui.moveTo(cx + 250, cy, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)

# 화살표 2: 아래쪽
pyautogui.moveTo(cx, cy + 120)
pyautogui.mouseDown()
pyautogui.moveTo(cx, cy + 250, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)
ss("11_arrows_with_ring")

# Text 도구
pyautogui.click(toolbar_x(5), tb_y)
time.sleep(0.3)

# 텍스트 1
pyautogui.click(cx + 180, cy - 20)
time.sleep(0.2)
pyautogui.typewrite("Product", interval=0.03)
pyautogui.press('enter')
time.sleep(0.2)

# 텍스트 2
pyautogui.click(cx + 10, cy + 180)
time.sleep(0.2)
pyautogui.typewrite("H_2O", interval=0.03)
pyautogui.press('enter')
time.sleep(0.3)

ss("12_text_with_arrows")

# ===== 테스트 8: 줌인으로 결합 간격 확인 =====
print("\n[8] 줌인으로 결합 그리드 스냅 확인...")
# Bond 도구
pyautogui.click(toolbar_x(2), tb_y)
time.sleep(0.2)

# 줌인 (큰 배율)
pyautogui.moveTo(cx, cy)
for _ in range(10):
    pyautogui.scroll(3, cx, cy)
    time.sleep(0.1)
ss("13_zoomed_in_grid")

# 결합 하나 그리기 (줌인 상태에서)
pyautogui.moveTo(cx - 30, cy)
pyautogui.mouseDown()
pyautogui.moveTo(cx + 30, cy, duration=0.3)
pyautogui.mouseUp()
time.sleep(0.3)
ss("14_bond_zoomed")

# 줌아웃 복귀
for _ in range(10):
    pyautogui.scroll(-3, cx, cy)
    time.sleep(0.1)

# ===== 완료 =====
print("\n" + "=" * 50)
print(f"테스트 완료! {ss_idx}개 스크린샷")
print("=" * 50)

proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()
